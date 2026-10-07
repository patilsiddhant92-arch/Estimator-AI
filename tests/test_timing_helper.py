"""The shared linear-time check (tests/timing.py) passes linear work and fails quadratic work, by growth alone."""
import pytest
import timing
from timing import growth, grows_faster, grows_linearly


def _linear(n):
    total = 0
    for i in range(n):
        total += i
    return total


def _quadratic(n):
    total = 0
    for i in range(n):
        for j in range(n):
            total += j
    return total


def test_linear_work_passes():
    assert grows_linearly(_linear, 20_000)


def test_quadratic_work_fails_every_time():
    assert growth(_quadratic, 400, runs=2) > 8          # grows_linearly is any(growth < 8): it fails


@pytest.mark.slow
def test_quadratic_work_is_detected_with_three_attempts_under_jitter_on_the_base_run(monkeypatch):
    monkeypatch.setattr(timing, "MIN_BASE", 0.03)         # the jitter is the point here, not the base size
    calls = [0]

    def jittery(n):                                      # the first calls (warm-up and the first small runs)
        calls[0] += 1                                    # take twice as long: a burst of load on the base run
        _quadratic(n)
        if calls[0] <= 12:
            _quadratic(n)
    assert grows_faster(jittery, 100, attempts=3)
