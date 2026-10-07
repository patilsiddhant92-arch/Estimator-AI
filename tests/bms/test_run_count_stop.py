"""A vision-count question refused `max_attempts` times stops the run at the count step with its "Stopped:"
message: the run does not go on to write the systems from skeletons that lack the vision count (RUN-3). Invented
job folder (test_run's), chat mode."""
from __future__ import annotations

import json

from test_run import _reach, job_folder  # noqa: F401  (job_folder is a fixture)

STOP = "Stopped: the request Count tags M-201 was refused 3 times. The answer leaves out a tile."


def _stop_the_count(monkeypatch):
    """The count question's ask ends in a stop (refused its last time); every other question is asked as usual."""
    from bms import ai
    from bms.counts_vision import COUNT_KIND

    real = ai._ask_checked

    def ask(transport, kind, *args, **kwargs):
        if kind == COUNT_KIND:
            raise ai.NoAnswer(STOP, waiting=False)
        return real(transport, kind, *args, **kwargs)

    monkeypatch.setattr(ai, "_ask_checked", ask)


def _kinds(cache):
    return {json.loads(p.read_text(encoding="utf-8"))["kind"]
            for p in (cache / "judge-chat" / "requests").glob("*.json")}


def test_a_count_question_refused_its_last_time_stops_the_run_at_the_count_step(job_folder, tmp_path, monkeypatch):
    from bms.run import estimate

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    assert _reach(job_folder, out, cache, "count").stage == "count"

    _stop_the_count(monkeypatch)
    result = estimate(job_folder, out, cache, "chat")

    assert result.status == "waiting" and result.stage == "count", result
    assert STOP in result.messages, result.messages
    assert "write_system" not in _kinds(cache)          # no system was written from a skeleton lacking its count
    state = json.loads((out / "run state.json").read_text(encoding="utf-8"))
    assert state["stage"] == "count" and STOP in state["messages"]


def test_a_count_stop_stops_every_run_until_the_question_is_answered(job_folder, tmp_path, monkeypatch):
    from bms.run import estimate

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out, cache = tmp_path / "out", tmp_path / "cache"
    _reach(job_folder, out, cache, "count")

    _stop_the_count(monkeypatch)
    estimate(job_folder, out, cache, "chat")
    again = estimate(job_folder, out, cache, "chat")
    assert again.stage == "count" and STOP in again.messages
    assert "write_system" not in _kinds(cache)
