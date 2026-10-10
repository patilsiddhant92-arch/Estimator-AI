"""The user guide's promise about an older page's decisions.json: a family change saved as words with no count in them
("4 pipe FCU": a number followed by other words is no count) stops the run at the decisions stage and says which
change it is; the estimator types a number on that card, saves again, and the next run goes on with that count.
Invented data only: the invented job folder of test_run.py."""
from __future__ import annotations

import copy
import json

from bms import run

from test_review_final import _cards, _decision, _drive
from test_run import job_folder  # noqa: F401  (a fixture)
from test_run_family_accept import _vav_count


def test_a_family_change_of_words_with_no_count_stops_the_run_and_a_typed_count_lets_it_go_on(job_folder, tmp_path,
                                                                                              monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _drive(job_folder, out, cache, [])
    family = next(c for c in _cards(out) if c["level"] == "family")
    older = _decision(family, "change", reason="4 pipe FCU")                 # the older page saved the words alone
    (out / "decisions.json").write_text(json.dumps([older]), encoding="utf-8")

    stopped = run.estimate(job_folder, out, cache, "chat")
    said = " ".join(stopped.messages)
    assert (stopped.status, stopped.stage, stopped.waiting) == ("waiting", "decisions", 0)
    assert stopped.proposal is None
    assert said.startswith("Stopped:") and "decisions.json" in said
    assert repr(family["family_name"]) in said and "'4 pipe FCU'" in said      # which change it is
    assert "whole number" in said and "review page" in said                    # and what to do

    count = dict(copy.deepcopy(family["count"]), value=5, others=[])
    typed = _decision(family, "change", count=count, reason="5 units")        # a number typed on that card
    (out / "decisions.json").write_text(json.dumps([typed]), encoding="utf-8")
    again = _drive(job_folder, out, cache, [])
    assert _vav_count(again, family) == 5
