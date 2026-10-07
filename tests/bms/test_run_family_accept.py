"""RUN-1 through the run: the estimator changes the VAV family count (4 -> 5) on the page, the run rewrites and
prints 5, the family card comes back, and the estimator accepts it. The next run still prints 5 and the history
keeps the change. Invented data only: the invented job folder of test_run.py."""
from __future__ import annotations

import copy
import json

from test_review_final import _cards, _decision, _drive, _job
from test_run import job_folder  # noqa: F401  (a fixture)


def _vav_count(result, family) -> int | None:
    system = next(s for s in _job(result)["systems"] if s["key"] == family["system_key"])
    return next(f for f in system["families"] if f["name"] == family["family_name"])["count"]["value"]


def test_a_family_accept_saved_after_a_count_change_keeps_the_changed_count(job_folder, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    family = next(c for c in _cards(out) if c["level"] == "family")
    count = dict(copy.deepcopy(family["count"]), value=5)
    (out / "decisions.json").write_text(json.dumps([_decision(family, "change", count=count, reason="5")]),
                                        encoding="utf-8")
    second = _drive(job_folder, out, cache, [])
    assert _vav_count(second, family) == 5

    again = next(c for c in _cards(out) if c["level"] == "family"     # the card comes back (others are kept)
                 and c["family_name"] == family["family_name"])
    (out / "decisions.json").write_text(json.dumps([_decision(again, "accept")]), encoding="utf-8")
    third = _drive(job_folder, out, cache, [])
    assert _vav_count(third, family) == 5
    history = json.loads((out / "decisions history.json").read_text(encoding="utf-8"))
    assert [(h["round"], h["decision"]["action"]) for h in history
            if h["decision"]["family_name"] == family["family_name"]] == [(1, "change"), (2, "accept")]
    assert next(h for h in history if h["decision"]["action"] == "change")["decision"]["count"]["value"] == 5


def test_a_count_the_estimator_typed_below_its_family_is_not_sent_to_the_revise(job_folder, tmp_path, monkeypatch):
    """AI-1 next to RUN-1: the estimator types 3 on the sensor line, which is counted from the VAV family (its
    quantity cites the family's source) while the family prints 4. The validator's "Never undershoot" finding on
    a line counted below its family is a check, never sent to the revise: the typed count stays and no "decision
    not honored" card is left."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    cards = _cards(out)
    family = next(c for c in cards if c["level"] == "family")
    sensor = next(c for c in cards if c["level"] == "device")
    typed = copy.deepcopy(sensor["device"])
    typed["quantity"] = dict(copy.deepcopy(family["count"]), value=3, others=[])
    (out / "decisions.json").write_text(json.dumps([_decision(sensor, "change", device=typed, reason="3")]),
                                        encoding="utf-8")
    second = _drive(job_folder, out, cache, [])
    system = next(s for s in _job(second)["systems"] if s["key"] == sensor["system_key"])
    assert [d["quantity"]["value"] for d in system["devices"] if d["id"] == sensor["device_id"]] == [3]
    assert not [f for f in second.findings if f.rule == "decision not honored"], second.findings

