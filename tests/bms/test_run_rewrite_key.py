"""RUN-2: the count rewrite is asked from the written system with only the family-count changes applied, so its
question does not change when the estimator later renames a line or accepts the family: the next run asks the
writer nothing. Invented data only: the invented job folder of test_run.py."""
from __future__ import annotations

import copy
import json

from bms import run
from test_review_final import _cards, _decision, _drive, _job
from test_run import answer_all, job_folder  # noqa: F401  (a fixture)


def _kinds(cache) -> list[str]:
    return [json.loads(p.read_text(encoding="utf-8"))["kind"]
            for p in sorted((cache / "judge-chat" / "requests").glob("*.json"))]


def _changed_count(job_folder, out, cache):
    """Run 1 to the end, then a VAV family count change (4 -> 5) to the end; the family card and the system."""
    _drive(job_folder, out, cache, [])
    family = next(c for c in _cards(out) if c["level"] == "family")
    count = dict(copy.deepcopy(family["count"]), value=5)
    (out / "decisions.json").write_text(json.dumps([_decision(family, "change", count=count, reason="5")]),
                                        encoding="utf-8")
    second = _drive(job_folder, out, cache, [])
    system = next(s for s in _job(second)["systems"] if s["key"] == family["system_key"])
    return family, system


def _asks_no_writer(job_folder, out, cache):
    """The next run asks no write_system question (no rewrite), then it ends."""
    result = run.estimate(job_folder, out, cache, "chat")
    assert "write_system" not in _kinds(cache), (result.stage, _kinds(cache))
    for _ in range(10):
        if result.status == "done":
            return result
        answer_all(cache)
        result = run.estimate(job_folder, out, cache, "chat")
        assert "write_system" not in _kinds(cache), (result.stage, _kinds(cache))
    raise AssertionError(result)


def test_a_rename_after_a_count_change_does_not_ask_the_writer_again(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    family, system = _changed_count(job_folder, out, cache)
    line = system["devices"][0]
    card = {"system_key": system["key"], "level": "device", "device_id": line["id"], "family_name": None,
            "finding_rule": None, "device": line}
    renamed = dict(copy.deepcopy(line), name="Room Temperature Sensor", flag="none")
    (out / "decisions.json").write_text(json.dumps([_decision(card, "change", device=renamed,
                                                              reason="Room Temperature Sensor")]), encoding="utf-8")
    result = _asks_no_writer(job_folder, out, cache)
    final = next(s for s in _job(result)["systems"] if s["key"] == system["key"])
    assert [d["name"] for d in final["devices"]] == ["Room Temperature Sensor"]
    assert next(f for f in final["families"] if f["name"] == family["family_name"])["count"]["value"] == 5
    assert not [f for f in result.findings if f.rule == "decision not honored"], result.findings


def test_a_family_accept_after_a_count_change_does_not_ask_the_writer_again(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    family, system = _changed_count(job_folder, out, cache)
    again = next(c for c in _cards(out) if c["level"] == "family" and c["family_name"] == family["family_name"])
    (out / "decisions.json").write_text(json.dumps([_decision(again, "accept")]), encoding="utf-8")
    result = _asks_no_writer(job_folder, out, cache)
    final = next(s for s in _job(result)["systems"] if s["key"] == system["key"])
    assert next(f for f in final["families"] if f["name"] == family["family_name"])["count"]["value"] == 5


def test_a_delete_after_a_count_change_does_not_ask_the_writer_again(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _family, system = _changed_count(job_folder, out, cache)
    line = system["devices"][0]
    card = {"system_key": system["key"], "level": "device", "device_id": line["id"], "family_name": None,
            "finding_rule": None, "device": line}
    (out / "decisions.json").write_text(json.dumps([_decision(card, "delete")]), encoding="utf-8")
    result = _asks_no_writer(job_folder, out, cache)
    final = next(s for s in _job(result)["systems"] if s["key"] == system["key"])
    assert [d["name"] for d in final["devices"] if d["name"] == line["name"]] == []
