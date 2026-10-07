"""A child process that failed to start on a loaded machine (exit 3221225794) is run again; nothing else is."""
import subprocess

import pytest

from procs import RESOURCE_ERROR, retrying


def _fake(codes):
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], codes[len(calls) - 1], stdout="out", stderr="err")
    return run, calls


def test_two_resource_errors_then_success_runs_three_times():
    run, calls = _fake([RESOURCE_ERROR, RESOURCE_ERROR, 0])
    pauses = []
    assert retrying(run, sleep=pauses.append)(["git", "init"], check=True).returncode == 0
    assert len(calls) == 3 and len(pauses) == 2
    assert all("check" not in kwargs for _, kwargs in calls)


def test_a_real_failure_is_not_tried_again_and_check_still_raises():
    run, calls = _fake([1, 0])
    assert retrying(run, sleep=lambda s: None)(["git", "x"]).returncode == 1 and len(calls) == 1
    run, calls = _fake([1])
    with pytest.raises(subprocess.CalledProcessError) as error:
        retrying(run, sleep=lambda s: None)(["git", "x"], check=True)
    assert error.value.returncode == 1 and error.value.stderr == "err" and len(calls) == 1


def test_three_resource_errors_are_returned_or_raised():
    run, calls = _fake([RESOURCE_ERROR] * 3)
    assert retrying(run, sleep=lambda s: None)(["x"]).returncode == RESOURCE_ERROR and len(calls) == 3
    run, calls = _fake([RESOURCE_ERROR] * 3)
    with pytest.raises(subprocess.CalledProcessError):
        retrying(run, sleep=lambda s: None)(["x"], check=True)
    assert len(calls) == 3


def test_every_test_runs_children_through_the_retry():
    assert getattr(subprocess.run, "retries_resource_errors", False)
    import sys
    assert subprocess.run([sys.executable, "-c", "pass"], check=True).returncode == 0
