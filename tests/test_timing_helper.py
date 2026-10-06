"""The shared linear-time check (tests/timing.py) passes linear work and fails quadratic work, by growth alone."""
from timing import growth, grows_linearly


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
